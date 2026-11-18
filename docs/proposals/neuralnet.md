# `neuralnet` — a neural network, in the two notations figures use

**Status: built** (task `t-9dddc873`, issue #174).

The owner asked for neural-network drawings, noting there are many. There are: a
fully connected figure of neurons, a flat LeNet-style strip of feature maps, AlexNet's
3D blocks, a paper's box-and-arrow architecture, Netron's operator graph. Most figures
in textbooks and papers are one of two, and those two say the same thing — the layers
of a network, in order — at two zoom levels. So one kind, two styles:

* **`neurons`** — the textbook's fully connected figure: each layer a column of
  circles, every neuron joined to every neuron of the next layer.
* **`blocks`** — a paper's architecture figure: each layer a box in sequence, its
  tensor shape beside it, skip connections round the layers they bypass, repeated
  blocks framed with `×N`.

Not built, and why: AlexNet-style 3D blocks (a picture of tensor volumes, whose sizes
the reader cannot compare: the 2D strip says the same in words), and arbitrary
branching (an encoder–decoder's cross-attention, branches inside branches): a graph of
operators is a `flow`, which already routes one. Inception's towers were added later at
the owner's request — see the answers below.

## The originals

The `find the originals` rule asks for at least two real figures. These were found by
web search; **the figures themselves were not opened** from this session, so what is
said of each is what the search results and their excerpts show.

1. **Nielsen, *Neural Networks and Deep Learning*, chapter 1, "The architecture of
   neural networks"** — *seen through a chapter summary and PDF copies found by search*
   ([pappubahry.com, notes on chapter 1](https://pappubahry.com/misc/neural/nielsen_1/)).
   784 input neurons (one per pixel of a 28×28 image), a hidden layer (15 in the figure,
   30 in the text) and 10 outputs; the figure draws the input layer cut, as its first and
   last neurons with dots between. This is `docs/reference/neuralnet-mnist.json`; a test
   computes the 784-30-10 network's 23,860 parameters.
2. **NN-SVG** (LeNail, JOSS 2019) — *seen as search results*
   ([JOSS paper](https://joss.theoj.org/papers/10.21105/joss.00747),
   [README](https://cdn.jsdelivr.net/gh/alexlenail/nn-svg@master/README.md)): three
   styles — FCNN (circles fully joined, the `neurons` style), LeNet (flat layer strips
   labelled with channels and size) and AlexNet (3D blocks).
3. **LeCun et al., 1998, LeNet-5** — *from the paper's well-known Figure 2, not opened*:
   INPUT 32×32, C1 6@28×28, S2 6@14×14, C3 16@10×10, S4 16@5×5, C5 120, F6 84, OUTPUT 10,
   named C (convolution), S (subsampling), F (full). This is
   `docs/reference/neuralnet-lenet.json`.
4. **He et al., 2015, ResNet, Figure 2 "Residual learning: a building block"** — *not
   opened*: x, two weight layers with a ReLU between, the identity shortcut round them
   into a ⊕, then a ReLU. This is `docs/reference/neuralnet-residual-block.json`.
5. **Vaswani et al., 2017, "Attention Is All You Need", Figure 1** — *the paper's text
   seen as a search result* ([arXiv](https://arxiv.org/pdf/1706.03762);
   [The Annotated Transformer](https://nlp.seas.harvard.edu/annotated-transformer)): the
   encoder reads from the bottom, a stack of N = 6 identical layers framed and marked
   `N×`, each self-attention then feed-forward, each wrapped in a residual connection
   and "Add & Norm". This is `docs/reference/neuralnet-transformer-encoder.json`.
6. **PlotNeuralNet** — *seen as search results*
   ([fork of the repository](https://github.com/singhay/PlotNeuralNet),
   [KDnuggets](https://www.kdnuggets.com/2020/12/generating-beautiful-neural-network-visualizations.html)):
   layers as blocks left to right with skip connections drawn over them.

## Decisions

* **Lines between neurons are headless** (`link`). A dense figure carries dozens; a head
  on each buries the circles. Nielsen and NN-SVG draw plain lines.
* **A layer past eight neurons is cut**: first three, three dots, last two, with
  `784 neurons` under its name. Labels are then refused (they cannot each be drawn).
* **Every circle is the size of the widest label**, as in `automaton`.
* **A skip branches off the arrow** leaving its `from`, as ResNet's and the
  Transformer's figures draw it, not out of the box. So a residual round a repeated
  block's layers starts inside its frame, and a skip whose ends are on either side of
  a frame's line is refused.
* **Fills by `type`**, through the theme's four class fills, keyed when there are two
  or more; a fifth type is refused.
* **Across, then down.** `blocks` runs across; when the boxes at their own widths do not
  fit, they share the canvas and wrap; when that does not fit either, the network runs
  down. An explicit `direction` is never changed.
* **The text form is a model summary**, as Keras's `summary()`: for `neurons` the
  parameters are computed (weights and biases of each fully connected layer).
* **Budget**: 16 layers, 6 skips, 3 repeats.

## Owner answers (task `t-0327828e`, issue #176)

* **Arrows in and out: yes.** `neurons` draws an arrow into each input neuron (not a
  bias unit) and out of each output neuron.
* **Branches: yes, as Inception needs them**, and other branching may stay refused.
  An entry `{"branches": [{"layers": [...]}, ...]}` draws 2–4 towers of 1–3 layers
  between the layer before (the split) and the layer after (the join), as GoogLeNet's
  Figure 2(b) (Szegedy et al., 2015, "Going deeper with convolutions": previous layer;
  1×1 conv; 1×1 then 3×3; 1×1 then 5×5; 3×3 max pool then 1×1; filter concatenation —
  from the paper's well-known figure, not opened from this session). This is
  `docs/reference/neuralnet-inception.json`. Still refused, each with the reason:
  branches first or last (nothing to split from or join at), two sets in a row,
  nesting, more than 4 branches or 3 layers in one, and ids or shapes inside a tower.
  A skip may still go round a set of branches (Inception-ResNet's shortcut).
